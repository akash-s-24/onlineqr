"use client"

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { BrutalButton } from '@/components/ui/brutal-button'
import { CandyButton } from '@/components/ui/candy-button'

export const AccordionDemo = () => (
  <Accordion className="w-full lg:w-[unset]" type="single" collapsible>
    <AccordionItem className="lg:w-[500px] max-w-full" value="item-1">
      <AccordionTrigger>Is it accessible?</AccordionTrigger>
      <AccordionContent>
        Yes. It adheres to the WAI-ARIA design pattern.
      </AccordionContent>
    </AccordionItem>
  </Accordion>
)

export default function Default() {
  return (
    <div className="flex min-h-screen w-full flex-col items-center justify-center gap-8 bg-background p-12">
      <div className="flex flex-wrap items-center justify-center gap-6">
        <BrutalButton>Deploy Doom</BrutalButton>
        <CandyButton>Register for Symposium</CandyButton>
      </div>

      <div className="w-full max-w-md">
        <AccordionDemo />
      </div>
    </div>
  )
}
