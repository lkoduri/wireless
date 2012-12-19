# Copyright (c) 2012 Jonathan Perry
# This code is released under the MIT license (see LICENSE file).
import wireless

class SpinalFactory(object):
    def make_encoder(self, codeSpec, packetLength):
        if codeSpec['type'] != 'spinal':
            return None
        
        spineLength = self._get_spine_length(codeSpec, packetLength)

        # get un-punctured encoder
        unpuncturedEncoder = self._make_unpunctured_encoder(codeSpec, spineLength)
        
        # Choose puncturing
        punc = self._get_puncturing(codeSpec, spineLength, forEncoder=True)
        
        # punctured encoder
        encoder = wireless.codes.MultiToSingleStreamEncoder(unpuncturedEncoder, punc)
    
        return encoder, wireless.vectorus

    def make_decoder(self, codeSpec, packetLength, decodeSpec, mapSpec, channelSpec):
        if codeSpec['type'] != 'spinal':
            return None
        if decodeSpec['type'] not in ['regular', 'lookahead', 'parallel']:
            return None
        
        spineLength = self._get_spine_length(codeSpec, packetLength)

        # make un-punctured decoder
        unpuncturedDecoder, valueType = self._make_unpunctured_decoder(codeSpec, 
                                                                       spineLength, 
                                                                       decodeSpec, 
                                                                       mapSpec, 
                                                                       channelSpec)
        
        
        # Get puncturing
        punc = self._get_puncturing(codeSpec, spineLength, forEncoder=False)

        PuncturedDecoderType = self._get_punctured_decoder_type(valueType)
    
        decoder = PuncturedDecoderType(unpuncturedDecoder,
                                       punc)
        
        # Choose whether an extended result is needed, and patch decoder
        #     if necessary
        if 'extendedResult' in decodeSpec:
            if decodeSpec['extendedResult'] == True:
                decoder.decode = unpuncturedDecoder.decodeExtended
    
        return decoder
    
    def make_protocol(self, protoSpec, codeSpec, packetLength):
        if protoSpec['type'] == 'faster':
            spineLength = self._get_spine_length(codeSpec, packetLength)
            punc = self._get_puncturing(codeSpec, spineLength)

            return FastFourwayProtocol(1,
                                       protoSpec['maxPasses'],
                                       punc)
        elif protoSpec['type'] == 'sequential':
            spineLength = self._get_spine_length(codeSpec, packetLength)
            
            if codeSpec['puncturing']['type'] != '8-way':
                raise RuntimeError, "unsupported puncturing schedule for sequential protocol"

            numSubpasses = protoSpec['maxPasses']
            numFullPasses = numSubpasses / 8
            numLastCodeStep = codeSpec['puncturing']['numLastCodeStep']
            numSymbolsFullPass = (spineLength - 1 + numLastCodeStep)
            maxSymbols = numFullPasses * numSymbolsFullPass
            if codeSpec['puncturing'].has_key('encoderToSymbolRate'):
                repeatRatio = codeSpec['puncturing']['encoderToSymbolRate'][1]
            else:
                repeatRatio = 1
            
            return wireless.codes.spinal.StridedProtocol(1, 
                                          spineLength,
                                          maxSymbols,
                                          numLastCodeStep,
                                          repeatRatio)
        else:
            return None


    def _make_unpunctured_encoder(self, codeSpec, spineLength):
        """
        Makes an un-punctured spinal encoder.
        @note assumes that codeSpec is a valid spinal code specification
        """
        codeFactory = wireless.codes.spinal.CodeFactory(codeSpec['k'],
                                         spineLength)
        # Choose hash
        if codeSpec['hash'] == 'salsa':
            codeFactory = codeFactory.salsa()
        elif codeSpec['hash'] == 'lookup3':
            codeFactory = codeFactory.lookup3()
        elif codeSpec['hash'] == 'one-at-a-time':
            codeFactory = codeFactory.oneAtATime()
        else:
            raise RuntimeError,"Unknown hash type %s" % codeSpec['hash']
        # Make unpunctured encoder
        unpuncturedEncoder = codeFactory.encoder()
        
        return unpuncturedEncoder

    def _make_unpunctured_decoder(self, codeSpec, spineLength, decodeSpec, mapSpec, channelSpec):
        """
        Makes an un-punctured spinal decoder.
        @return: a pair (decoder, inputType) where decoder is a decoder instance, and inputType
            is the type of the decoder input
        @note assumes that codeSpec is a valid spinal code specification
        """
        codeFactory = wireless.codes.spinal.CodeFactory(codeSpec['k'],
                                         spineLength)
        # Choose hash
        if codeSpec['hash'] == 'salsa':
            codeFactory = codeFactory.salsa()
        elif codeSpec['hash'] == 'lookup3':
            codeFactory = codeFactory.lookup3()
        elif codeSpec['hash'] == 'one-at-a-time':
            codeFactory = codeFactory.oneAtATime()
        else:
            raise RuntimeError,"Unknown hash type %s" % codeSpec['hash']
            
        # Choose channel transformation
        if channelSpec['type'] in ['AWGN', 'AWGN-1D', 'BSC','transparent-coherence-symbol']:
            if mapSpec['type'] == 'linear':
                codeFactory = codeFactory.linear(mapSpec['bitsPerSymbol'],
                                                 mapSpec['precisionBits'])
                valueType = wireless.Symbol
            elif mapSpec['type'] == 'trunc-norm-v2':
                codeFactory = codeFactory.gaussian(mapSpec['bitsPerSymbol'],
                                                   mapSpec['precisionBits'],
                                                   mapSpec['numStandardDevs'])
                valueType = wireless.Symbol
            else:
                raise RuntimeError, 'unknown mapper'
            
        elif channelSpec['type'] in ['AWGN-soft']:
            if mapSpec['type'] == 'soft':
                codeFactory = codeFactory.soft(mapSpec['bitsPerSymbol'])
                valueType = wireless.SoftSymbol
            else:
                raise RuntimeError, 'unknown mapper'
        elif channelSpec['type'] == 'coherence-fading':
            codeFactory = codeFactory.coherence(mapSpec['bitsPerSymbol'])
            valueType = wireless.FadingSymbol
        else:
            raise RuntimeError, 'unknown channel'
        
        # Choose search algorithm
        if decodeSpec['type'] == 'regular':
            # beam search
            unpuncturedDecoder = codeFactory.beamDecoder(
                                                1,
                                                decodeSpec['beamWidth'],
                                                decodeSpec['maxPasses'],
                                                decodeSpec['maxPasses'])
        elif decodeSpec['type'] == 'lookahead':
            # beam search
            unpuncturedDecoder = codeFactory.lookaheadBeamDecoder(
                                                decodeSpec['beamWidth'],
                                                decodeSpec['lookaheadDepth'],
                                                decodeSpec['maxPasses'],
                                                decodeSpec['maxPasses'])
        elif decodeSpec['type'] in ['parallel']:
            # beam search
            unpuncturedDecoder = codeFactory.beamDecoder(
                                                decodeSpec['alpha'],
                                                decodeSpec['beta'],
                                                decodeSpec['maxPasses'],
                                                decodeSpec['maxPasses'])
        else:
            raise RuntimeError, 'unknown decoder type %s' % decodeSpec['type']
        
        return unpuncturedDecoder, valueType

    @staticmethod
    def _get_punctured_decoder_type(valueType):
        """
        Returns the punctured adaptor type for a decoder with given input value types
        """
        if valueType is wireless.Symbol:
            return wireless.codes.MultiToSingleStreamDecoder_Symbol
        elif valueType is wireless.SoftSymbol:
            return wireless.codes.MultiToSingleStreamDecoder_SoftSymbol
        elif valueType is wireless.FadingSymbol:
            return wireless.codes.MultiToSingleStreamDecoder_FadingSymbol
        else:
            raise RuntimeError, "Unknown value type"


    @staticmethod
    def _get_spine_length(codeSpec, packetLength):
        # calculate number of code steps
        if packetLength % codeSpec['k'] != 0:
            raise RuntimeError, 'packet length not multiple of k'
        return (packetLength / codeSpec['k'])
    
    @staticmethod
    def _get_puncturing(codeSpec, spineLength, forEncoder):
        if codeSpec['type'] != 'spinal':
            raise RuntimeError, "Puncturing for non-spinal codes unimplemented"
        
        # Choose puncturing
        import wireless
        if codeSpec['puncturing']['type'] == '8-way':
            puncturing = wireless.codes.StridedPuncturingSchedule(
                                    spineLength,
                                    codeSpec['puncturing']['numLastCodeStep'])
        elif codeSpec['puncturing']['type'] == 'static':
            puncturing = wireless.codes.StaticPuncturingSchedule()
            schedule = wireless.vectorus(codeSpec['puncturing']['schedule'])
            puncturing.set(schedule)
        else:
            raise RuntimeError, 'unknown puncturing type %s' % codeSpec['puncturing']['type'] 
    
        
        # Choose the repetition ratio for the puncturing
        if codeSpec['puncturing'].has_key('encoderToSymbolRate'):
            encoderRate, symbolRate = codeSpec['puncturing']['encoderToSymbolRate']
            if forEncoder:
                repeatRatio = encoderRate
            else:
                repeatRatio = symbolRate
        else:
            repeatRatio = 1
    
        # Wrap the puncturing schedule with repetition, if neccessary
        if repeatRatio != 1:
            return wireless.codes.RepeatingPuncturingSchedule(puncturing, 
                                                      repeatRatio)
        else:
            return puncturing